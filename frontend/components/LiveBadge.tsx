export function LiveBadge({ isLive }: { isLive: boolean }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 10px', borderRadius: 980, fontSize: 10,
      fontWeight: 700, letterSpacing: 1.5, textTransform: 'uppercase',
      background: isLive ? 'rgba(0,210,100,0.12)' : 'rgba(255,180,0,0.12)',
      border: `1px solid ${isLive ? 'rgba(0,210,100,0.3)' : 'rgba(255,180,0,0.3)'}`,
      color: isLive ? 'rgb(0,210,100)' : 'rgb(255,180,0)',
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: '50%',
        background: 'currentColor',
        boxShadow: isLive ? '0 0 6px rgb(0,210,100)' : 'none',
      }} />
      {isLive ? 'LIVE' : 'MOCK'}
    </span>
  );
}
