import { NextRequest, NextResponse } from 'next/server';
import { Agent, fetch as undiciFetch } from 'undici';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

const longTimeoutAgent = new Agent({
  headersTimeout: 30_000,
  bodyTimeout: 30_000,
});

/**
 * GET /api/chat/pipeline/[session_id] — Get current pipeline state.
 *
 * Proxies to the Python backend's /chat/pipeline/{session_id} endpoint.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ session_id: string }> }
) {
  try {
    const { session_id } = await params;

    if (!session_id) {
      return NextResponse.json(
        { error: 'session_id is required' },
        { status: 400 }
      );
    }

    const targetUrl = `${AGENT_API_URL}/chat/pipeline/${session_id}`;

    const response = await undiciFetch(targetUrl, {
      method: 'GET',
      dispatcher: longTimeoutAgent,
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Backend error: ${errorText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error('Pipeline state API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
