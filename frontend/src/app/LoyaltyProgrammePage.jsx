import { useState } from "react";

const FAQ = [
  ["When do I get my Super Coins?", "Coins are credited after your order is delivered and confirmed, not when you place it."],
  ["How long do coins last?", "Each credit expires 365 days after it is earned. Older coins are used first, so they never get stuck behind newer ones."],
  ["Why do some products earn more coins?", "The store can set a higher rate on selected products or categories. When a product earns a special rate, you'll see the exact coins on its card and page."],
  ["Can I use coins at checkout?", "Not yet. One Super Coin is meant to equal ₹1, but checkout redemption will switch on only after balance and accounting controls are in place. Keep collecting in the meantime."],
  ["Where can I see my balance?", "Open My Account and choose Loyalty Card & Coins. Verify an order with your email and order reference to see your card, balance, and history."],
];

export default function LoyaltyProgrammePage({ rate = 1, onShop, onAccount }) {
  const [amount, setAmount] = useState("1000");
  const perHundred = Number(rate) > 0 ? Number(rate) : 0;
  const spend = Math.max(0, Number(amount) || 0);
  const coins = Math.floor(spend / 100 * perHundred);
  const examples = [500, 1000, 2500];
  return (
    <div className="sb-loy">
      <span className="storefront-kicker">CUSTOMER REWARDS</span>
      <h1>Loyalty Programme</h1>
      <p className="sb-loy-lead">Every eligible order earns Super Coins. They add up quietly in the background, so shopping with us pays you back.</p>

      <div className="sb-loy-facts">
        <div><strong>{perHundred || "—"}</strong><span>coin per ₹100 spent</span></div>
        <div><strong>₹1</strong><span>intended value of 1 coin</span></div>
        <div><strong>365</strong><span>days before a coin expires</span></div>
        <div><strong>After</strong><span>delivery is confirmed</span></div>
      </div>

      <h2>How it works</h2>
      <ol className="sb-loy-steps">
        <li><b>Shop</b><span>Add anything to your basket. Look for the "Earn Super Coins" tag on products.</span></li>
        <li><b>Get it delivered</b><span>Your coins are credited once delivery is confirmed.</span></li>
        <li><b>Track your coins</b><span>See your balance and history in My Account.</span></li>
        <li><b>Spend them</b><span>Redemption at checkout is coming soon.</span></li>
      </ol>

      <h2>Work out your coins</h2>
      <div className="sb-loy-calc">
        <label>Order value (₹)
          <input type="number" min="0" step="50" inputMode="numeric" value={amount} onChange={e => setAmount(e.target.value)} />
        </label>
        <div className="sb-loy-result" aria-live="polite">
          {perHundred ? <><strong>{coins}</strong><span>Super Coins{coins ? " (worth about ₹" + coins + ")" : ""}</span></> : <span>The earning rate isn't available right now. Check back soon.</span>}
        </div>
      </div>
      {perHundred > 0 && (
        <div className="sb-loy-table" role="table" aria-label="Example earnings">
          {examples.map(value => (
            <div role="row" key={value}><span role="cell">₹{value.toLocaleString("en-IN")} order</span><span role="cell">{Math.floor(value / 100 * perHundred)} coins</span></div>
          ))}
        </div>
      )}
      <p className="sb-loy-small">Estimates use the standard rate. Products or categories with a special rate show their own coins. Taxes, delivery, and other non-eligible charges may not count.</p>

      <h2>Good to know</h2>
      <ul className="sb-loy-list">
        <li>Coins are credited only after delivery is confirmed.</li>
        <li>Each credit expires 365 days after it is earned, and the oldest coins are used first.</li>
        <li>Special product and category rates are shown on the product itself.</li>
        <li>Checkout redemption isn't enabled yet.</li>
      </ul>

      <h2>Common questions</h2>
      <div className="sb-loy-faq">
        {FAQ.map(([question, answer]) => (
          <details key={question}><summary>{question}</summary><p>{answer}</p></details>
        ))}
      </div>

      <div className="sb-loy-actions">
        <button type="button" className="storefront-primary" onClick={onAccount}>Check my coins</button>
        <button type="button" className="storefront-secondary sb-loy-secondary" onClick={onShop}>Start shopping</button>
      </div>
    </div>
  );
}
