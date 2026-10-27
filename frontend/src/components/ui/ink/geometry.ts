// Path and label helpers for ink diagrams.

/** An orthogonal connector from (x1, y1) to (x2, y2), turning at `mx`. */
export function elbow(x1: number, y1: number, x2: number, y2: number, mx = (x1 + x2) / 2) {
  return `M${x1},${y1} H${mx} V${y2} H${x2}`
}

/** A smooth connector from (x1, y1) to (x2, y2). */
export function curve(x1: number, y1: number, x2: number, y2: number) {
  const m = (x1 + x2) / 2
  return `M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}`
}

/** Fits a label into a node: long text is cut with an ellipsis. */
export function clip(text: string, max: number) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}
