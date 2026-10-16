const BASE_DELAY_MS = 1000

export function retryDelay(attempt: number, random: () => number = Math.random): number {
  return random() * BASE_DELAY_MS * 2 ** (attempt - 1)
}
