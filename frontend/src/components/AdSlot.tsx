import { useEffect, useRef } from 'react'

/** AdSense slot when VITE_ADSENSE_ID is set; otherwise a self-hosted sponsor slot. */
export default function AdSlot({ slot = 'auto', compact = false }: { slot?: string; compact?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const publisher = import.meta.env.VITE_ADSENSE_ID as string | undefined
  const sponsorUrl = import.meta.env.VITE_AD_LINK as string | undefined
  const sponsorText = (import.meta.env.VITE_AD_TEXT as string | undefined) || 'Sponsored'

  useEffect(() => {
    if (!publisher || !ref.current) return
    const ins = ref.current.querySelector('ins.adsbygoogle')
    if (!ins || ins.getAttribute('data-adsbygoogle-status')) return
    try { (window.adsbygoogle ||= []).push({}) } catch { /* ad blocked */ }
  }, [publisher, slot])

  if (publisher) {
    return (
      <div ref={ref} className={`ad-slot ${compact ? 'compact' : ''}`}>
        <ins className="adsbygoogle"
             style={{ display: 'block' }}
             data-ad-client={publisher}
             data-ad-slot={slot}
             data-ad-format="auto"
             data-full-width-responsive="true" />
      </div>
    )
  }

  return (
    <a className={`ad-slot sponsor ${compact ? 'compact' : ''}`}
       href={sponsorUrl || '#'}
       target={sponsorUrl ? '_blank' : undefined}
       rel="noreferrer"
       onClick={e => { if (!sponsorUrl) e.preventDefault() }}>
      <span className="ad-label">AD</span>
      <span>{sponsorText}</span>
      <small>{sponsorUrl ? new URL(sponsorUrl).hostname : 'Configure VITE_AD_LINK'}</small>
    </a>
  )
}
