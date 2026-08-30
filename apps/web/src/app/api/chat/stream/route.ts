import { NextRequest, NextResponse } from 'next/server';
import { Agent, fetch as undiciFetch } from 'undici';

// Python agent server address
const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

// Create an Agent configured with long timeout
const longTimeoutAgent = new Agent({
  // Headers timeout: 2 minutes (120 seconds)
  headersTimeout: 120_000,
  // Response body timeout: 10 minutes (600 seconds) - This is the key setting to prevent BodyTimeoutError
  bodyTimeout: 600_000,
  // Keep-alive timeout: 30 minutes (1800 seconds)
  keepAliveTimeout: 1800_000,
  // Maximum keep-alive timeout: 30 minutes (1800 seconds)
  keepAliveMaxTimeout: 1800_000,
  // Connection timeout threshold: 1 minute
  keepAliveTimeoutThreshold: 60_000,
});

/**
 * GET /api/chat/stream - Stream responses from Python agent
 */
export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const prompt = searchParams.get('prompt');
    const sessionId = searchParams.get('sessionId');
    const accessCode = searchParams.get('accessCode');
    const projectId = searchParams.get('projectId');
    const projectName = searchParams.get('projectName');

    if (!prompt) {
      return NextResponse.json(
        { error: 'Prompt is required' },
        { status: 400 }
      );
    }

    const targetUrl = new URL(`${AGENT_API_URL}/chat/stream`);
    targetUrl.searchParams.set('prompt', prompt);
    if (sessionId) {
      targetUrl.searchParams.set('session_id', sessionId);
    }
    if (accessCode) {
      targetUrl.searchParams.set('accessCode', accessCode);
    }
    if (projectId) {
      targetUrl.searchParams.set('project_id', projectId);
    }
    if (projectName) {
      targetUrl.searchParams.set('project_name', projectName);
    }
    // Signal that the request originates from the frontend editor
    targetUrl.searchParams.set('client', 'editor');

    // Forward request to Python agent's streaming interface, using undici's fetch with long timeout configuration
    const response = await undiciFetch(targetUrl.toString(), {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream',
      },
      dispatcher: longTimeoutAgent,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Agent API error:', errorText);
      return NextResponse.json(
        { error: `Agent API error: ${errorText}` },
        { status: response.status }
      );
    }

    // Return streaming response
    // Convert undici's ReadableStream to Next.js compatible format and add heartbeat mechanism
    const stream = new ReadableStream({
      async start(controller) {
        const reader = response.body?.getReader();
        if (!reader) {
          controller.close();
          return;
        }
        
        // Add flag to track controller state and prevent duplicate closure
        let isClosed = false;
        
        // Heartbeat interval: send heartbeat every 20 seconds
        const heartbeatInterval = setInterval(() => {
          try {
            // Check if controller is closed to avoid writing to a closed controller
            if (isClosed) {
              clearInterval(heartbeatInterval);
              return;
            }
            const heartbeatData = `data: ${JSON.stringify({ type: 'heartbeat', timestamp: Date.now() })}\n\n`;
            controller.enqueue(new TextEncoder().encode(heartbeatData));
          } catch (error) {
            console.error('Error sending heartbeat:', error);
            clearInterval(heartbeatInterval);
          }
        }, 20000);
        
        try {
          while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
              console.log('Stream reading completed');
              clearInterval(heartbeatInterval);
              // Use flag to prevent duplicate controller closure
              if (!isClosed) {
                isClosed = true;
                controller.close();
              }
              break;
            }
            
            // Only write data if controller is not closed
            if (!isClosed && value) {
              controller.enqueue(value);
              // Log received data for debugging
              const text = new TextDecoder().decode(value);
              if (text.includes('"type"')) {
                console.log('Forwarding SSE event:', text.substring(0, 100));
              }
            }
          }
        } catch (error) {
          console.error('Error in stream reading:', error);
          clearInterval(heartbeatInterval);
          // Use flag to prevent duplicate controller closure
          if (!isClosed) {
            isClosed = true;
            controller.error(error);
          }
        }
      },
    });
    
    return new NextResponse(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
    });
  } catch (error) {
    console.error('Chat stream API error:', error);
    
    // Handle undici timeout errors and other network errors
    if (error instanceof Error) {
      // undici timeout error types
      if (error.name === 'HeadersTimeoutError' || error.name === 'BodyTimeoutError' ||
          error.name === 'TimeoutError' || error.message.includes('timeout')) {
        return NextResponse.json(
          { error: 'Request timeout: The video generation task took too long to complete. The timeout has been extended to 20 minutes for headers and 30 minutes for response body. Please try again or reduce the complexity of your request.' },
          { status: 408 }
        );
      }
      
      if (error.name === 'AbortError') {
        return NextResponse.json(
          { error: 'Request was aborted' },
          { status: 499 }
        );
      }
      
      // undici connection error
      if (error.name === 'ConnectTimeoutError') {
        return NextResponse.json(
          { error: 'Connection timeout: Unable to establish connection to the backend service.' },
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