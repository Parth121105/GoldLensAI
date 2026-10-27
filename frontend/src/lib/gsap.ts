// GSAP is used for one thing only: chart line drawing (components/charts/TimeChart.tsx).
// Tile entrances, route changes and disclosures stay in Motion.
import { useGSAP } from '@gsap/react'
import { gsap } from 'gsap'
import { CustomEase } from 'gsap/CustomEase'

gsap.registerPlugin(useGSAP, CustomEase)

/** The strong ease-out used for UI entrances: cubic-bezier(0.23, 1, 0.32, 1). */
export const EASE_OUT = CustomEase.create('ui-out', '0.23,1,0.32,1')

export const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(REDUCED_MOTION).matches
}

export { gsap, useGSAP }
