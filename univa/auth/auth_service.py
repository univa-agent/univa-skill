"""
Access code management service
"""

import json
import os
from typing import Optional, List, Dict
from datetime import datetime
from .models import AccessCodeInfo, AuthConfig
import uuid
import logging

logger = logging.getLogger(__name__)


class AuthService:
    """Access code management service"""
    
    def __init__(self, config_file: str):
        """
        Initialize access code management service
        
        Args:
            config_file: Configuration file path
        """
        self.config_file = config_file
        self.config: AuthConfig = self._load_config()
        logger.info(f"AuthService initialized with config file: {config_file}")
        
    def _load_config(self) -> AuthConfig:
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Convert access_codes data to AccessCodeInfo objects
                    if 'access_codes' in data:
                        access_codes = {}
                        for code, info in data['access_codes'].items():
                            # Convert date strings to datetime objects
                            if 'created_at' in info and isinstance(info['created_at'], str):
                                info['created_at'] = datetime.fromisoformat(info['created_at'].replace('Z', '+00:00'))
                            if 'last_used' in info and info['last_used'] and isinstance(info['last_used'], str):
                                info['last_used'] = datetime.fromisoformat(info['last_used'].replace('Z', '+00:00'))
                            access_codes[code] = AccessCodeInfo(**info)
                        data['access_codes'] = access_codes
                    
                    config = AuthConfig(**data)
                    logger.info(f"Loaded {len(config.access_codes)} access codes from config")
                    return config
            except Exception as e:
                logger.error(f"Failed to load auth config: {e}")
                logger.info("Creating new auth config")
                return AuthConfig()
        else:
            logger.info(f"Config file not found, creating new auth config")
            return AuthConfig()
    
    def _save_config(self):
        """Save configuration to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # Convert to serializable dictionary
            data = {
                'version': self.config.version,
                'access_codes': {},
                'settings': self.config.settings
            }
            
            for code, info in self.config.access_codes.items():
                data['access_codes'][code] = {
                    'access_code': info.access_code,
                    'user_id': info.user_id,
                    'description': info.description,
                    'created_at': info.created_at.isoformat() if info.created_at else None,
                    'enabled': info.enabled,
                    'last_used': info.last_used.isoformat() if info.last_used else None,
                    'usage_count': info.usage_count,
                    'max_conversations': info.max_conversations,
                    'conversation_count': info.conversation_count
                }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved auth config to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save auth config: {e}")
            raise
    
    def validate_access_code(self, access_code: str) -> Optional[str]:
        """
        Validate access code and return user_id
        
        Args:
            access_code: Access code
            
        Returns:
            user_id if valid, None otherwise
        """
        if not access_code or access_code not in self.config.access_codes:
            logger.debug(f"Access code not found: {access_code[:8] if access_code else 'None'}...")
            return None
        
        code_info = self.config.access_codes[access_code]
        if not code_info.enabled:
            logger.warning(f"Access code disabled: {access_code[:8]}... for user {code_info.user_id}")
            return None
        
        # Update usage statistics
        code_info.last_used = datetime.utcnow()
        code_info.usage_count += 1
        self._save_config()
        
        logger.debug(f"Access code validated: user_id={code_info.user_id}")
        return code_info.user_id
    
    def add_access_code(
        self,
        user_id: str,
        description: str = "",
        access_code: Optional[str] = None,
        max_conversations: Optional[int] = None
    ) -> str:
        """
        Add new access code
        
        Args:
            user_id: User ID
            description: Description
            access_code: Optional custom access code, auto-generated if not provided
            max_conversations: Max conversation limit, None means unlimited
            
        Returns:
            Generated access code
            
        Raises:
            ValueError: If access code already exists
        """
        if access_code is None:
            access_code = str(uuid.uuid4())
        
        if access_code in self.config.access_codes:
            raise ValueError(f"Access code already exists: {access_code}")
        
        code_info = AccessCodeInfo(
            access_code=access_code,
            user_id=user_id,
            description=description,
            created_at=datetime.utcnow(),
            max_conversations=max_conversations
        )
        
        self.config.access_codes[access_code] = code_info
        self._save_config()
        
        logger.info(f"Added access code for user {user_id}: {access_code} (max_conversations={max_conversations})")
        return access_code
    
    def remove_access_code(self, access_code: str) -> bool:
        """
        Delete access code
        
        Args:
            access_code: Access code
            
        Returns:
            True if removed, False if not found
        """
        if access_code not in self.config.access_codes:
            logger.warning(f"Access code not found for removal: {access_code[:8]}...")
            return False
        
        user_id = self.config.access_codes[access_code].user_id
        del self.config.access_codes[access_code]
        self._save_config()
        
        logger.info(f"Removed access code for user {user_id}: {access_code}")
        return True
    
    def enable_access_code(self, access_code: str, enabled: bool) -> bool:
        """
        Enable/disable access code
        
        Args:
            access_code: Access code
            enabled: True to enable, False to disable
            
        Returns:
            True if updated, False if not found
        """
        if access_code not in self.config.access_codes:
            logger.warning(f"Access code not found for enable/disable: {access_code[:8]}...")
            return False
        
        self.config.access_codes[access_code].enabled = enabled
        self._save_config()
        
        action = "enabled" if enabled else "disabled"
        user_id = self.config.access_codes[access_code].user_id
        logger.info(f"{action.capitalize()} access code for user {user_id}: {access_code}")
        return True
    
    def list_access_codes(self) -> List[Dict]:
        """
        List all access codes
        
        Returns:
            List of access code information
        """
        return [
            {
                "access_code": code,
                "user_id": info.user_id,
                "description": info.description,
                "created_at": info.created_at.isoformat() if info.created_at else None,
                "enabled": info.enabled,
                "last_used": info.last_used.isoformat() if info.last_used else None,
                "usage_count": info.usage_count,
                "max_conversations": info.max_conversations,
                "conversation_count": info.conversation_count
            }
            for code, info in self.config.access_codes.items()
        ]
    
    def get_access_code_info(self, access_code: str) -> Optional[Dict]:
        """
        Get access code information
        
        Args:
            access_code: Access code
            
        Returns:
            Access code information dictionary, None if not found
        """
        if access_code not in self.config.access_codes:
            return None
        
        info = self.config.access_codes[access_code]
        return {
            "access_code": access_code,
            "user_id": info.user_id,
            "description": info.description,
            "created_at": info.created_at.isoformat() if info.created_at else None,
            "enabled": info.enabled,
            "last_used": info.last_used.isoformat() if info.last_used else None,
            "usage_count": info.usage_count,
            "max_conversations": info.max_conversations,
            "conversation_count": info.conversation_count
        }
    
    def get_user_access_codes(self, user_id: str) -> List[Dict]:
        """
        Get all access codes for a specific user
        
        Args:
            user_id: User ID
            
        Returns:
            List of access codes for that user
        """
        return [
            {
                "access_code": code,
                "user_id": info.user_id,
                "description": info.description,
                "created_at": info.created_at.isoformat() if info.created_at else None,
                "enabled": info.enabled,
                "last_used": info.last_used.isoformat() if info.last_used else None,
                "usage_count": info.usage_count,
                "max_conversations": info.max_conversations,
                "conversation_count": info.conversation_count
            }
            for code, info in self.config.access_codes.items()
            if info.user_id == user_id
        ]
    
    def check_conversation_limit(self, access_code: str) -> bool:
        """
        Check if access code has available conversation count
        
        Args:
            access_code: Access code
            
        Returns:
            True if can start new conversation, False if limit reached
        """
        if access_code not in self.config.access_codes:
            logger.warning(f"Access code not found for conversation limit check: {access_code[:8]}...")
            return False
        
        code_info = self.config.access_codes[access_code]
        
        # If no limit is set, return True
        if code_info.max_conversations is None:
            return True
        
        # Check if limit has been reached
        if code_info.conversation_count >= code_info.max_conversations:
            logger.warning(
                f"Conversation limit reached for access code {access_code[:8]}... "
                f"({code_info.conversation_count}/{code_info.max_conversations})"
            )
            return False
        
        return True
    
    def increment_conversation_count(self, access_code: str) -> bool:
        """
        Increment conversation count for access code
        
        Args:
            access_code: Access code
            
        Returns:
            True if incremented successfully, False if access code not found
        """
        if access_code not in self.config.access_codes:
            logger.warning(f"Access code not found for conversation increment: {access_code[:8]}...")
            return False
        
        code_info = self.config.access_codes[access_code]
        code_info.conversation_count += 1
        self._save_config()
        
        logger.info(
            f"Incremented conversation count for access code {access_code[:8]}... "
            f"({code_info.conversation_count}/{code_info.max_conversations or 'unlimited'})"
        )
        return True
    
    def set_conversation_limit(self, access_code: str, max_conversations: Optional[int]) -> bool:
        """
        Set conversation limit for access code
        
        Args:
            access_code: Access code
            max_conversations: Max conversations, None means unlimited
            
        Returns:
            True if updated successfully, False if access code not found
        """
        if access_code not in self.config.access_codes:
            logger.warning(f"Access code not found for setting conversation limit: {access_code[:8]}...")
            return False
        
        self.config.access_codes[access_code].max_conversations = max_conversations
        self._save_config()
        
        logger.info(
            f"Set conversation limit for access code {access_code[:8]}... to "
            f"{max_conversations or 'unlimited'}"
        )
        return True
    
    def reset_conversation_count(self, access_code: str) -> bool:
        """
        Reset conversation count for access code
        
        Args:
            access_code: Access code
            
        Returns:
            True if reset successfully, False if access code not found
        """
        if access_code not in self.config.access_codes:
            logger.warning(f"Access code not found for conversation count reset: {access_code[:8]}...")
            return False
        
        self.config.access_codes[access_code].conversation_count = 0
        self._save_config()
        
        logger.info(f"Reset conversation count for access code {access_code[:8]}...")
        return True