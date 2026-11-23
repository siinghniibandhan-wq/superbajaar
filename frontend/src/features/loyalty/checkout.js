export function clampRedeemCoins(requested, maximum) {
  const requestedCoins = Math.floor(Number(requested));
  const maximumCoins = Math.max(0, Math.floor(Number(maximum)));
  if (!Number.isFinite(requestedCoins) || !Number.isFinite(maximumCoins)) return 0;
  return Math.max(0, Math.min(requestedCoins, maximumCoins));
}
