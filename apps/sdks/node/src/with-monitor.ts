/**
 * ``withMonitor`` — wrap an async function so every call pings Whycron.
 *
 * Sends a ``started`` ping before the function runs, then a ``succeeded``
 * or ``failed`` ping after based on whether the promise resolves or
 * rejects. Captures the error message + stack as the ``logs`` payload on
 * failure and records the wall-clock duration in milliseconds.
 *
 * The wrapper never swallows the underlying error — rejections still
 * propagate to the caller after the ping is sent. Network errors during
 * the ping itself never break the wrapped function (they're logged via
 * ``console.warn``).
 *
 * Example::
 *
 *   import { Whycron, withMonitor } from "whycron";
 *
 *   const wc = new Whycron();
 *   const nightlyBackup = withMonitor("wcr_abc123def", wc, async () => {
 *     // your work here
 *   });
 *
 *   await nightlyBackup();
 */

import { Whycron } from "./client.js";

let defaultClient: Whycron | undefined;

function getDefaultClient(): Whycron {
  if (!defaultClient) {
    defaultClient = new Whycron();
  }
  return defaultClient;
}

export interface WithMonitorOptions {
  /** Override the default client (e.g. for a custom baseUrl or test injection). */
  client?: Whycron;
  /** Send the rejection's stack/message as the logs payload. Default true. */
  captureLogs?: boolean;
  /** Tail logs to this many chars before sending. Default 4000. */
  logTailChars?: number;
}

/**
 * Form A — wrap a single async function call with start/end pings.
 *
 * Returns a function with the same signature; call it like the original.
 */
export function withMonitor<Args extends unknown[], R>(
  pingToken: string,
  fn: (...args: Args) => Promise<R>,
  options?: WithMonitorOptions,
): (...args: Args) => Promise<R>;

/**
 * Form B — explicit-client signature for cases where you want to be
 * extra-clear about which client is used.
 */
export function withMonitor<Args extends unknown[], R>(
  pingToken: string,
  client: Whycron,
  fn: (...args: Args) => Promise<R>,
  options?: WithMonitorOptions,
): (...args: Args) => Promise<R>;

export function withMonitor<Args extends unknown[], R>(
  pingToken: string,
  fnOrClient: ((...args: Args) => Promise<R>) | Whycron,
  fnOrOptions?: ((...args: Args) => Promise<R>) | WithMonitorOptions,
  maybeOptions?: WithMonitorOptions,
): (...args: Args) => Promise<R> {
  let fn: (...args: Args) => Promise<R>;
  let options: WithMonitorOptions;

  if (typeof fnOrClient === "function") {
    fn = fnOrClient;
    options = (fnOrOptions as WithMonitorOptions) ?? {};
  } else {
    fn = fnOrOptions as (...args: Args) => Promise<R>;
    options = { client: fnOrClient, ...(maybeOptions ?? {}) };
  }

  const client = options.client ?? getDefaultClient();
  const captureLogs = options.captureLogs ?? true;
  const logTail = options.logTailChars ?? 4000;

  return async (...args: Args): Promise<R> => {
    await safePing(client, pingToken, { state: "started" });
    const startedAt = performance.now();
    try {
      const result = await fn(...args);
      const durationMs = Math.round(performance.now() - startedAt);
      await safePing(client, pingToken, {
        state: "succeeded",
        exitCode: 0,
        durationMs,
      });
      return result;
    } catch (err) {
      const durationMs = Math.round(performance.now() - startedAt);
      const logs = captureLogs ? formatError(err).slice(-logTail) : undefined;
      await safePing(client, pingToken, {
        state: "failed",
        exitCode: 1,
        durationMs,
        ...(logs ? { logs } : {}),
      });
      throw err;
    }
  };
}

async function safePing(
  client: Whycron,
  token: string,
  options: Parameters<Whycron["ping"]>[1],
): Promise<void> {
  try {
    await client.ping(token, options);
  } catch (err) {
    // Never let a ping failure break the wrapped function.
    // eslint-disable-next-line no-console
    console.warn(
      "[whycron] ping failed:",
      err instanceof Error ? err.message : String(err),
    );
  }
}

function formatError(err: unknown): string {
  if (err instanceof Error) {
    return err.stack ?? `${err.name}: ${err.message}`;
  }
  return String(err);
}
