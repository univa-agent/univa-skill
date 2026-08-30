import { NextRequest, NextResponse } from 'next/server';
import { Agent, fetch as undiciFetch } from 'undici';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

const longTimeoutAgent = new Agent({
  headersTimeout: 120_000,
  bodyTimeout: 600_000,
  keepAliveTimeout: 1800_000,
  keepAliveMaxTimeout: 1800_000,
  keepAliveTimeoutThreshold: 60_000,
});

/**
 * POST /api/chat/resume — Resume a suspended interactive pipeline.
 *
 * Proxies to the Python backend's /chat/resume endpoint.
 * The backend returns JSON with the resumed pipeline state.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { session_id, continuation_token, user_input } = body;

    if (!session_id || !user_input) {
      return NextResponse.json(
        { error: 'session_id and user_input are required' },
        { status: 400 }
      );
    }

    const targetUrl = `${AGENT_API_URL}/chat/resume`;

    const response = await undiciFetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id,
        continuation_token: continuation_token || '',
        user_input,
      }),
      dispatcher: longTimeoutAgent,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Resume API error:', errorText);
      return NextResponse.json(
        { error: `Backend error: ${errorText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error('Chat resume API error:', error);

    if (error instanceof Error) {
      if (error.name === 'ConnectTimeoutError') {
        return NextResponse.json(
          { error: 'Connection timeout: Unable to reach backend service.' },
          { status: 503 }
        );
      }
    }

    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
