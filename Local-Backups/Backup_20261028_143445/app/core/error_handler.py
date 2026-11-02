import logging
from functools import wraps

logger = logging.getLogger(__name__)

def quantum_error_handler(func):
    """Decorator that catches all errors and returns user-friendly messages"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            
            # AI API Errors
            if "rate limit" in error_msg or "429" in error_msg:
                return "⚠️ *System Overloaded*\nThe Quantum Nexus is processing high demand. Please try again in 30 seconds."
            
            if "api key" in error_msg or "401" in error_msg:
                logger.critical("API KEY ERROR: Check your .env file")
                return "⚠️ *Configuration Error*\nThe system administrator has been notified. Please try again later."
            
            if "not found" in error_msg or "404" in error_msg:
                logger.error(f"Resource not found: {e}")
                return "⚠️ *Service Unavailable*\nThe AI vision engine is temporarily offline. Maintenance in progress."
            
            # Image Processing Errors
            if "bytes" in error_msg or "image" in error_msg:
                return "⚠️ *Image Processing Error*\nPlease upload a clear, standard chart image (JPG/PNG)."
            
            # Generic Fallback
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            return "⚠️ *Analysis Interrupted*\nThe Quantum Nexus encountered an unexpected condition. Please retry."
    
    return wrapper