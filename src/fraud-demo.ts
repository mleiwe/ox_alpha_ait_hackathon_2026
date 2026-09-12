export interface UserAccount {
  id: string;
  status: "active" | "suspended";
  failedLogins: number;
  chargebacks: number;
  emailVerified: boolean;
  accountAgeDays: number;
  ordersLast24h: number;
}

export interface RiskAssessment {
  accountId: string;
  reliability: number;
  flagged: boolean;
  reasons: string[];
}

export type ReviewDecision = "pending" | "suspended" | "cleared";

export interface ReviewQueueEntry {
  accountId: string;
  reliability: number;
  reasons: string[];
  decision: ReviewDecision;
  decidedBy: "human" | null;
}

export const REVIEW_THRESHOLD = 40;

export const reviewQueue: ReviewQueueEntry[] = [];

export function evaluateReliability(account: UserAccount): number {
  let reliability = 100;
  reliability -= Math.min(account.failedLogins * 5, 25);
  reliability -= Math.min(account.chargebacks * 15, 45);
  if (!account.emailVerified) reliability -= 10;
  if (account.accountAgeDays < 7) reliability -= 10;
  reliability -= Math.min(Math.max(account.ordersLast24h - 20, 0) * 2, 20);
  return Math.max(0, Math.min(100, reliability));
}

function buildReasons(account: UserAccount): string[] {
  const reasons: string[] = [];
  if (account.failedLogins > 0) reasons.push(`${account.failedLogins} failed logins`);
  if (account.chargebacks > 0) reasons.push(`${account.chargebacks} chargebacks`);
  if (!account.emailVerified) reasons.push("email not verified");
  if (account.accountAgeDays < 7) reasons.push("account younger than 7 days");
  if (account.ordersLast24h > 20) reasons.push("high order velocity in last 24h");
  return reasons;
}

export function assessAccounts(accounts: UserAccount[]): RiskAssessment[] {
  return accounts.map((account) => {
    const reliability = evaluateReliability(account);
    const reasons = buildReasons(account);
    const flagged = reliability < REVIEW_THRESHOLD;
    if (flagged) {
      reviewQueue.push({
        accountId: account.id,
        reliability,
        reasons,
        decision: "pending",
        decidedBy: null,
      });
    }
    return { accountId: account.id, reliability, flagged, reasons };
  });
}

export function applyHumanDecision(entry: ReviewQueueEntry, account: UserAccount, suspend: boolean): void {
  if (suspend) {
    account.status = "suspended";
    entry.decision = "suspended";
  } else {
    entry.decision = "cleared";
  }
  entry.decidedBy = "human";
}
