import { NextRequest, NextResponse } from 'next/server';

// Python agent server address
const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

/**
 * POST /api/chat - Send user prompt to Python agent
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { prompt, sessionId } = body;

    // Validate input
    if (!prompt || typeof prompt !== 'string') {
      return NextResponse.json(
        { error: 'Prompt is required and must be a string' },
        { status: 400 }
      );
    }

    // Forward request to Python agent
    const response = await fetch(`${AGENT_API_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt,
        session_id: sessionId,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Agent API error:', errorText);
      return NextResponse.json(
        { error: `Agent API error: ${errorText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    
    return NextResponse.json({
      success: true,
      sessionId: data.session_id,
      response: data.response,
    });
  } catch (error) {
    console.error('Chat API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * GET /api/chat/stream - Stream responses from Python agent
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const prompt = searchParams.get('prompt');
    const sessionId = searchParams.get('sessionId');

    // Validate input
    if (!prompt) {
      return NextResponse.json(
        { error: 'Prompt is required' },
        { status: 400 }
      );
    }

    // Forward request to Python agent's streaming interface
    const response = await fetch(
      `${AGENT_API_URL}/chat/stream?prompt=${encodeURIComponent(prompt)}${sessionId ? `&session_id=${sessionId}` : ''}`,
      {
        method: 'GET',
        headers: {
          'Accept': 'text/event-stream',
        },
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Agent API error:', errorText);
      return NextResponse.json(
        { error: `Agent API error: ${errorText}` },
        { status: response.status }
      );
    }

    // Return streaming response
    return new NextResponse(response.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    console.error('Chat stream API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}