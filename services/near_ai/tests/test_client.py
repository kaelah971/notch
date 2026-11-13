"""Tests for the NEAR AI OpenAI-compatible client boundary."""

from __future__ import annotations

import json
import unittest

from services.near_ai.client import (
    NearAIAuthError,
    NearAIClient,
    NearAIModelUnavailable,
    NearAIProviderError,
    NearAIRateLimitError,
    NearAIResponseError,
)
from services.near_ai.config import NearAIConfig


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected provider call")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _json(data, status=200, headers=None):
    return status, headers or {}, json.dumps(data)


def _client(transport, *, key="test-key", model="z-ai/glm-5.3-flash"):
    config = NearAIConfig(api_key=key, model=model, rate_limit_seconds=0)
    return NearAIClient(config=config, transport=transport, sleep=lambda _: None)


MODEL = {
    "id": "z-ai/glm-5.3-flash",
    "object": "model",
    "owned_by": "nearai",
    "pricing": {"input": 0.08, "output": 0.5},
    "context_length": 1048576,
    "max_output_length": 1048576,
    "supported_features": ["structured_outputs", "json_mode"],
    "supported_sampling_parameters": ["temperature", "max_tokens"],
    "is_ready": True,
}


class ClientTests(unittest.TestCase):
    def test_models_and_selection(self):
        transport = FakeTransport([
            _json({"object": "list", "data": [MODEL]}),
            _json({"object": "list", "data": [MODEL]}),
        ])
        client = _client(transport)
        models = client.list_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].model_id, "z-ai/glm-5.3-flash")
        self.assertEqual(models[0].price_per_million(), (0.08, 0.5))
        self.assertEqual(models[0].supported_sampling_parameters, ["temperature", "max_tokens"])
        selected = client.select_model()
        self.assertEqual(selected.model_id, "z-ai/glm-5.3-flash")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0]["headers"]["Authorization"], "Bearer test-key")

    def test_missing_model(self):
        transport = FakeTransport([_json({"object": "list", "data": [MODEL]})])
        client = _client(transport)
        with self.assertRaises(NearAIModelUnavailable):
            client.select_model("missing/model")

    def test_chat_json_request_and_usage(self):
        transport = FakeTransport(
            [
                _json(
                    {
                        "model": "z-ai/glm-5.3-flash",
                        "choices": [{"message": {"role": "assistant", "content": json.dumps({"headline": "ok"})}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    },
                    headers={"x-request-id": "req-1"},
                )
            ]
        )
        client = _client(transport)
        completion = client.chat_json(
            model="z-ai/glm-5.3-flash",
            system_prompt="system",
            user_prompt="user",
        )
        self.assertEqual(completion.content["headline"], "ok")
        self.assertEqual(completion.usage["total_tokens"], 15)
        self.assertEqual(completion.request_id, "req-1")
        self.assertEqual(completion.diagnostics["http_status"], 200)
        self.assertEqual(completion.diagnostics["finish_reason"], None)
        self.assertTrue(completion.diagnostics["message_content_present"])
        self.assertEqual(completion.diagnostics["message_content_chars"], len('{"headline": "ok"}'))
        self.assertEqual(completion.diagnostics["usage"]["completion_tokens"], 5)
        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertTrue(call["url"].endswith("/chat/completions"))
        self.assertEqual(call["body"]["model"], "z-ai/glm-5.3-flash")
        self.assertEqual(call["body"]["messages"][0]["role"], "system")
        self.assertEqual(call["body"]["max_tokens"], 4096)
        self.assertEqual(call["body"]["response_format"], {"type": "json_object"})
        self.assertNotIn("test-key", json.dumps(call["body"]))

    def test_code_fenced_json_is_parsed(self):
        transport = FakeTransport(
            [
                _json(
                    {
                        "choices": [{"message": {"content": "```json\n{\"headline\":\"ok\"}\n```"}}],
                        "usage": {},
                    }
                )
            ]
        )
        completion = _client(transport).chat_json(
            model="z-ai/glm-5.3-flash", system_prompt="s", user_prompt="u"
        )
        self.assertEqual(completion.content["headline"], "ok")

    def test_auth_error(self):
        transport = FakeTransport([(401, {}, json.dumps({"message": "bad key"}))])
        with self.assertRaises(NearAIAuthError):
            _client(transport).list_models()
        self.assertEqual(len(transport.calls), 1)

    def test_rate_limit_error_no_retry(self):
        transport = FakeTransport([(429, {}, json.dumps({"message": "slow down"}))])
        with self.assertRaises(NearAIRateLimitError):
            _client(transport).list_models()
        self.assertEqual(len(transport.calls), 1)

    def test_provider_error_no_retry(self):
        transport = FakeTransport([(503, {}, json.dumps({"message": "unavailable"}))])
        with self.assertRaises(NearAIProviderError):
            _client(transport).list_models()
        self.assertEqual(len(transport.calls), 1)

    def test_invalid_json_response(self):
        transport = FakeTransport([(200, {}, "not-json")])
        with self.assertRaises(NearAIResponseError):
            _client(transport).list_models()

    def test_invalid_chat_json(self):
        transport = FakeTransport(
            [
                _json(
                    {
                        "choices": [{"message": {"content": "not-json"}, "finish_reason": "stop"}],
                        "usage": {},
                    }
                )
            ]
        )
        with self.assertRaises(NearAIResponseError) as caught:
            _client(transport).chat_json(
                model="z-ai/glm-5.3-flash", system_prompt="s", user_prompt="u"
            )
        self.assertEqual(caught.exception.diagnostics["finish_reason"], "stop")
        self.assertEqual(caught.exception.diagnostics["message_content_chars"], len("not-json"))
        self.assertIsNone(caught.exception.as_dict()["body_snippet"])

    def test_empty_content_with_length_finish_reason_reports_reasoning_budget(self):
        transport = FakeTransport(
            [
                _json(
                    {
                        "choices": [
                            {
                                "message": {"content": "", "reasoning_content": "private reasoning"},
                                "finish_reason": "length",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 40,
                            "completion_tokens": 4096,
                            "total_tokens": 4136,
                            "completion_tokens_details": {"reasoning_tokens": 4090},
                        },
                    },
                    headers={"x-request-id": "req-length"},
                )
            ]
        )
        with self.assertRaises(NearAIResponseError) as caught:
            _client(transport).chat_json(
                model="z-ai/glm-5.3-flash", system_prompt="s", user_prompt="u"
            )
        error = caught.exception
        self.assertIn("finish_reason=length", str(error))
        self.assertEqual(error.status, 200)
        self.assertEqual(error.diagnostics["request_id"], "req-length")
        self.assertTrue(error.diagnostics["reasoning_content_present"])
        self.assertEqual(error.diagnostics["reasoning_content_chars"], len("private reasoning"))
        self.assertEqual(error.diagnostics["usage"]["reasoning_tokens"], 4090)
        self.assertEqual(error.diagnostics["max_tokens_requested"], 4096)

    def test_reasoning_without_final_answer_is_reported_without_exposing_reasoning(self):
        transport = FakeTransport(
            [
                _json(
                    {
                        "choices": [
                            {
                                "message": {"reasoning_content": "private reasoning"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"completion_tokens": 12},
                    }
                )
            ]
        )
        with self.assertRaises(NearAIResponseError) as caught:
            _client(transport).chat_json(
                model="z-ai/glm-5.3-flash", system_prompt="s", user_prompt="u"
            )
        error = caught.exception
        self.assertIn("reasoning_content was present", str(error))
        self.assertNotIn("private reasoning", repr(error.as_dict()))
        self.assertEqual(error.diagnostics["finish_reason"], "stop")

    def test_missing_content_is_reported(self):
        transport = FakeTransport(
            [_json({"choices": [{"message": {}, "finish_reason": "stop"}], "usage": {}})]
        )
        with self.assertRaises(NearAIResponseError) as caught:
            _client(transport).chat_json(
                model="z-ai/glm-5.3-flash", system_prompt="s", user_prompt="u"
            )
        self.assertTrue(caught.exception.diagnostics["message_content_empty"])
        self.assertFalse(caught.exception.diagnostics["reasoning_content_present"])

    def test_dict_content_is_accepted_as_structured_json(self):
        transport = FakeTransport(
            [_json({"choices": [{"message": {"content": {"headline": "ok"}}}], "usage": {}})]
        )
        completion = _client(transport).chat_json(
            model="z-ai/glm-5.3-flash", system_prompt="s", user_prompt="u"
        )
        self.assertEqual(completion.content, {"headline": "ok"})
        self.assertEqual(completion.diagnostics["message_content_type"], "dict")

    def test_no_key_does_not_add_authorization(self):
        transport = FakeTransport([_json({"object": "list", "data": [MODEL]})])
        client = _client(transport, key=None)
        client.list_models()
        self.assertNotIn("Authorization", transport.calls[0]["headers"])


if __name__ == "__main__":
    unittest.main()
