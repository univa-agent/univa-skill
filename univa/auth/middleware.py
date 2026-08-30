"""
FastAPI authentication middleware
"""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable, Set
import logging

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI authentication middleware"""
    
    # Public endpoints list (no authentication required)
    PUBLIC_ENDPOINTS: Set[str] = {
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc"
    }
    
    # Admin endpoints list (requires admin access code, not in access code list)
    ADMIN_ENDPOINTS_PREFIX: Set[str] = {
        "/admin/"
    }
    
    def __init__(self, app, auth_service, auth_enabled: bool = True):
        """
        Initialize authentication middleware
        
        Args:
            app: FastAPI application instance
            auth_service: AuthService instance
            auth_enabled: Whether to enable authentication
        """
        super().__init__(app)
        self.auth_service = auth_service
        self.auth_enabled = auth_enabled
        logger.info(f"AuthMiddleware initialized (auth_enabled={auth_enabled})")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Handle request
        
        Args:
            request: Request object
            call_next: Next handler
            
        Returns:
            Response object
        """
        # Allow OPTIONS requests through (CORS preflight requests)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # If authentication is not enabled, pass through directly
        if not self.auth_enabled:
            return await call_next(request)
        
        # Check if it's a public endpoint
        if self._is_public_endpoint(request.url.path):
            return await call_next(request)
        
        # Extract access code - support from Header or URL parameter
        # Prioritize from Header, if not available then from URL parameter (for EventSource)
        access_code = (
            request.headers.get("X-Access-Code") or
            request.headers.get("x-access-code") or
            request.query_params.get("accessCode")
        )
        
        if not access_code:
            logger.warning(f"Missing access code for path: {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "Missing X-Access-Code header or accessCode query parameter"
                }
            )
        
        # Check if it's an admin endpoint
        if self._is_admin_endpoint(request.url.path):
            # Admin endpoint: only need to inject access code, verified by verify_admin function
            # Don't call validate_access_code because admin access code is not in the access code list
            request.state.access_code = access_code
            request.state.user_id = "admin"  # Temporary value; actual verification is handled in verify_admin.
            logger.info(f"Admin endpoint access: path={request.url.path}, code={access_code[:8]}...")
            return await call_next(request)
        
        # Regular endpoint: validate access code
        user_id = self.auth_service.validate_access_code(access_code)
        if not user_id:
            logger.warning(f"Invalid access code: {access_code[:8]}... for path: {request.url.path}")
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Forbidden",
                    "message": "Invalid or disabled access code"
                }
            )
        
        # Inject user_id into request state
        request.state.user_id = user_id
        request.state.access_code = access_code
        
        logger.debug(f"Auth success: user_id={user_id}, path={request.url.path}")
        
        # Continue processing request
        return await call_next(request)
    
    def _is_public_endpoint(self, path: str) -> bool:
        """
        Check if it's a public endpoint
        
        Args:
            path: Request path
            
        Returns:
            True if public, False otherwise
        """
        # Exact match
        if path in self.PUBLIC_ENDPOINTS:
            return True
        
        # Prefix match (for /docs, /redoc and other static resources)
        for endpoint in self.PUBLIC_ENDPOINTS:
            if path.startswith(endpoint + "/"):
                return True
        
        return False
    
    def _is_admin_endpoint(self, path: str) -> bool:
        """
        Check if it's an admin endpoint
        
        Args:
            path: Request path
            
        Returns:
            True if admin endpoint, False otherwise
        """
        # Prefix match
        for prefix in self.ADMIN_ENDPOINTS_PREFIX:
            if path.startswith(prefix):
                return True
        
        return False