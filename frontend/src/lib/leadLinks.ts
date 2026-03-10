type LeadLike = {
  source: string
  username: string
  profile_url: string | null
  evidence_posts: { url: string }[]
  evidence_urls: string[]
}

export function sourceLabel(source: string): string {
  return source === 'facebook' ? 'Facebook' : 'Reddit'
}

export function toFacebookGroupUrl(url: string | null | undefined): string | null {
  if (!url) return null
  const m = url.match(/^https?:\/\/(?:www\.)?facebook\.com\/groups\/([^/?#]+)/i)
  if (!m) return null
  return `https://www.facebook.com/groups/${m[1]}/`
}

export function leadProfileHref(lead: LeadLike): string | null {
  if (lead.profile_url) {
    if (lead.source === 'facebook') {
      return toFacebookGroupUrl(lead.profile_url) || lead.profile_url
    }
    return lead.profile_url
  }
  if (lead.source === 'reddit') return `https://reddit.com/u/${lead.username}`
  return (
    toFacebookGroupUrl(lead.evidence_posts[0]?.url) ||
    toFacebookGroupUrl(lead.evidence_urls[0]) ||
    lead.evidence_posts[0]?.url ||
    lead.evidence_urls[0] ||
    null
  )
}
