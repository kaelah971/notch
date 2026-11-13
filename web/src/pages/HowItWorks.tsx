import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { NotchMark } from '../components/icons'
import { Footer } from '../components/Footer'
import './HowItWorks.css'

/** Static explainer. Every statement mirrors the deployed contract and S3B oracle behaviour. */
export function HowItWorks() {
  const { hash } = useLocation()
  useEffect(() => { if (hash) document.getElementById(hash.slice(1))?.scrollIntoView() }, [hash])
  return (
    <div className="hiw">
      <header className="hiw-nav"><Link to="/" aria-label="Notch home"><NotchMark width={26} height={26} /></Link><Link to="/app/markets" className="btn btn-white" style={{ height: 36, fontSize: 14 }}>Explore Markets</Link></header>
      <main className="hiw-main">
        <h1>How Notch works</h1>
        <p className="hiw-lede">Notch markets ask where public attention goes next — measured by Wikipedia pageviews — and settle from evidence anyone can check.</p>

        <section id="how">
          <h2>Make your call</h2>
          <p>Each market has fixed outcomes (UP/DOWN, or two topics in a Trend Battle). You stake test-USDC on the outcome you expect. Your wallet signs the transaction; Notch never holds your keys.</p>
          <p>Markets are <strong>pooled</strong>: all stakes go into one escrow. When a market resolves, everyone who backed the winning outcome shares the whole pool in proportion to their stake: <span className="mono">payout = your stake × total pool ÷ winning pool</span>. The protocol fee is currently 0%.</p>
          <p>There is no order book and no price. The split of stakes between outcomes shows what participants have put in — it is not a probability. Positions can’t be sold early; they settle at resolution.</p>
        </section>

        <section id="rules">
          <h2>Market rules</h2>
          <p>Before a market opens, its rule is frozen: the data source (Wikimedia Pageviews, en.wikipedia.org, all-access, user agents, daily UTC), the exact article, the baseline and target days, the formula and threshold, and what happens if data is missing. The rule’s SHA-256 hash is stored in the market contract, so it can’t change after entries open.</p>
          <p>A Trend Trading market resolves UP if the target day’s views grow by at least the threshold versus the baseline day. A Trend Battle compares normalized growth of two topics; a difference within the stated tolerance is a tie and the market is voided.</p>
        </section>

        <section id="evidence">
          <h2>Evidence &amp; resolution</h2>
          <p>After the resolution window, the oracle fetches the pageviews, computes the outcome with integer-only arithmetic, and records an evidence receipt. Its digest is written onchain with the result. Each market page shows the evidence digest and whether it matches the onchain hash.</p>
          <p>If data is missing or a battle ties, the market is voided and every stake can be refunded in full. AI-written briefs are context only — they never decide an outcome.</p>
        </section>

        <section id="risk">
          <h2>Risk information</h2>
          <ul>
            <li>Notch runs on <strong>NEAR Testnet</strong>. Test tokens have no monetary value.</li>
            <li>You can lose the full amount you stake on an outcome that doesn’t win.</li>
            <li>Payouts depend on how much others stake on each side by the time entries close; the final pool split is unknown when you enter.</li>
            <li>Transactions are public on the blockchain. Hiding a profile in Notch does not hide onchain activity.</li>
            <li>“Resolved demonstration” markets replayed past data to prove the pipeline. They were never predictions and don’t count toward performance.</li>
          </ul>
        </section>
      </main>
      <Footer />
    </div>
  )
}
