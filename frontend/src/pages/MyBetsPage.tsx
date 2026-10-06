export function MyBetsPage() {
  return (
    <>
      <h1>My Bets</h1>
      <div className="empty-state">
        <p>You haven’t placed any bets.</p>
        <p className="hint">Betting arrives in phase 3.</p>
      </div>
    </>
  );
}
