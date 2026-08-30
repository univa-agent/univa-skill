import { NextRequest, NextResponse } from 'next/server';

// Python agent server address
const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

/**
 * GET /api/access-code/status - Get access code status information
 */
export async function GET(req: NextRequest) {
  try {
    // Get access code from request header
    const accessCode = req.headers.get('X-Access-Code');

    if (!accessCode) {
      return NextResponse.json(
        { error: 'Access code is required' },
        { status: 401 }
      );
    }

    // Forward request to Python agent's access code status interface
    const targetUrl = `${AGENT_API_URL}/access-code/status`;
    
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'X-Access-Code': accessCode,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Agent API error:', errorText);
      
      // Return corresponding error status
      if (response.status === 401) {
        return NextResponse.json(
          { error: 'Invalid access code' },
          { status: 401 }
        );
      }
      
      if (response.status === 404) {
        return NextResponse.json(
          { error: 'Access code not found' },
          { status: 404 }
        );
      }
      
      return NextResponse.json(
        { error: `Agent API error: ${errorText}` },
        { status: response.status }
      );
    }

    // Return access code status information
    const data = await response.json();
    return NextResponse.json(data);
    
  } catch (error) {
    console.error('Access code status API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}