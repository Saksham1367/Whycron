/**
 * Whycron SDK error hierarchy.
 */

export class WhycronError extends Error {
  override readonly name: string = "WhycronError";
  constructor(message: string) {
    super(message);
  }
}

export class WhycronAPIError extends WhycronError {
  override readonly name: string = "WhycronAPIError";
  readonly statusCode: number;
  readonly body: unknown;

  constructor(statusCode: number, message: string, body?: unknown) {
    super(`[${statusCode}] ${message}`);
    this.statusCode = statusCode;
    this.body = body;
  }
}

export class WhycronAuthError extends WhycronAPIError {
  override readonly name: string = "WhycronAuthError";
}

export class WhycronNotFoundError extends WhycronAPIError {
  override readonly name: string = "WhycronNotFoundError";
}

export class WhycronRateLimitedError extends WhycronAPIError {
  override readonly name: string = "WhycronRateLimitedError";
}
