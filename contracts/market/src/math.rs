//! Deterministic integer arithmetic for pooled settlement.
//!
//! `payout = floor(stake * total_pool / winning_pool)`
//!
//! The intermediate product can exceed `u128` even when the final payout is a
//! valid `u128`, so the multiplication/division is performed with a 256-bit
//! integer and the result is range-checked before being returned.

/// Clippy emits style lints from inside the `uint` macro expansion; scoping
/// the generated code to a module keeps the crate lint-clean.
#[allow(clippy::manual_div_ceil, clippy::assign_op_pattern)]
mod u256 {
    use uint::construct_uint;

    construct_uint! {
        /// 256-bit unsigned integer, used only for the mul-div intermediate.
        pub struct U256(4);
    }
}

use u256::U256;

/// `floor(a * b / d)` with a 256-bit intermediate.
///
/// Panics if `d == 0` or if the mathematical result does not fit in `u128`.
/// Consumers only call this with `stake <= winning_pool` and
/// `total_pool <= u128::MAX`, so the result always fits.
pub fn mul_div_floor(a: u128, b: u128, d: u128) -> u128 {
    assert!(d > 0, "ERR_MATH_DIVISION_BY_ZERO");
    let product = U256::from(a) * U256::from(b);
    let result = product / U256::from(d);
    assert!(result <= U256::from(u128::MAX), "ERR_MATH_OVERFLOW");
    result.low_u128()
}

/// Fully collateralized pooled payout. Fees are zero.
///
/// Returns 0 when the stake or the winning pool is empty; callers treat a
/// market with an empty winning pool as invalid and must void it instead.
pub fn pooled_payout(stake: u128, total_pool: u128, winning_pool: u128) -> u128 {
    if stake == 0 || winning_pool == 0 {
        return 0;
    }
    mul_div_floor(stake, total_pool, winning_pool)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exact_and_rounding_cases() {
        assert_eq!(mul_div_floor(100, 400, 300), 133);
        assert_eq!(mul_div_floor(200, 400, 300), 266);
        assert_eq!(mul_div_floor(1, 3, 2), 1);
        assert_eq!(mul_div_floor(2, 3, 2), 3);
        assert_eq!(mul_div_floor(1, 1, 1), 1);
        assert_eq!(mul_div_floor(0, 400, 300), 0);
    }

    #[test]
    fn single_sided_market_returns_own_stake() {
        assert_eq!(pooled_payout(100, 100, 100), 100);
    }

    #[test]
    fn empty_pools_pay_nothing() {
        assert_eq!(pooled_payout(0, 100, 100), 0);
        assert_eq!(pooled_payout(100, 100, 0), 0);
        assert_eq!(pooled_payout(100, 0, 0), 0);
    }

    #[test]
    fn handles_product_that_overflows_u128() {
        let half = u128::MAX / 2;
        assert_eq!(mul_div_floor(half, half, half), half);
        assert_eq!(mul_div_floor(u128::MAX, u128::MAX, u128::MAX), u128::MAX);
    }

    #[test]
    fn fuzz_like_conservation_matrix() {
        // Deterministic sweep over small pools: winners' floored payouts must
        // never exceed the escrow, and each payout must be >= the stake when
        // the winning side is at most the whole pool.
        for a_total in 1u128..=40 {
            for b_total in 0u128..=40 {
                let escrow = a_total + b_total;
                for stake in 0..=a_total {
                    let payout = pooled_payout(stake, escrow, a_total);
                    assert!(payout <= escrow);
                    if stake > 0 {
                        assert_eq!(payout, stake * escrow / a_total);
                        assert!(payout >= stake);
                    }
                }
            }
        }
    }

    #[test]
    fn combined_payouts_never_exceed_pool() {
        for a in 1u128..=30 {
            for b in 0u128..=30 {
                let total = a + b;
                let mut paid = 0u128;
                for _ in 1..=a {
                    // `a` independent positions of one base unit each.
                    paid += pooled_payout(1, total, a);
                }
                assert!(paid <= total, "a={a} b={b} paid={paid} total={total}");
            }
        }
    }

    #[test]
    #[should_panic(expected = "ERR_MATH_DIVISION_BY_ZERO")]
    fn division_by_zero_panics() {
        mul_div_floor(1, 1, 0);
    }
}
