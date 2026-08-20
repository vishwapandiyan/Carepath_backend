"""
Chat Title Generator Service
Uses Google Gemini API to auto-generate chat titles
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import google.generativeai as genai
from app.config import settings

logger = logging.getLogger(__name__)

# Configure Gemini client
genai.configure(api_key=settings.google_api_key)


class TitleGeneratorService:
    """Service for generating chat titles using AI"""
    
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        """
        Initialize title generator
        
        Args:
            model_name: Gemini model to use
        """
        self.model_name = model_name
    
    async def generate_title(self, first_message: str, max_words: int = 7) -> str:
        """
        Generate a concise title from the first user message
        
        Args:
            first_message: First user message in the chat
            max_words: Maximum words in title (default: 7)
        
        Returns:
            str: Generated title
        
        Fallback: If API fails, returns date-based title
        """
        try:
            # Create prompt
            prompt = f"""Generate a concise {max_words}-word or less title for this healthcare conversation.
The title should capture the main topic clearly and be suitable for a chat history list.

Rules:
- Maximum {max_words} words
- Clear and descriptive
- No quotation marks
- Professional healthcare context
- Title case

User message: "{first_message}"

Return ONLY the title, nothing else."""
            
            # Call Gemini API
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,  # Low temperature for consistent titles
                    max_output_tokens=50,
                )
            )
            
            response = await model.generate_content_async(prompt)
            title = response.text.strip() if response.text else None
            
            if not title:
                logger.warning("Gemini returned empty title, using fallback")
                return self._generate_fallback_title()
            
            # Clean up title
            title = title.strip('"\'')  # Remove quotes if present
            title = title[:500]  # Enforce max length
            
            logger.info(f"Generated title: {title}")
            return title
            
        except Exception as e:
            logger.error(f"Title generation failed: {e}, using fallback")
            return self._generate_fallback_title()
    
    def _generate_fallback_title(self) -> str:
        """
        Generate fallback title based on current date
        
        Returns:
            str: Date-based title
        """
        return f"Chat from {datetime.utcnow().strftime('%B %d, %Y')}"
    
    async def generate_title_with_context(
        self,
        first_message: str,
        patient_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate title with additional context
        
        Args:
            first_message: First user message
            patient_id: Optional patient ID for context
            context: Optional additional context
        
        Returns:
            str: Generated title
        """
        try:
            context_info = []
            if patient_id:
                context_info.append(f"Patient: {patient_id}")
            if context:
                prediction_type = context.get("prediction_type")
                if prediction_type:
                    context_info.append(f"Topic: {prediction_type}")
            
            context_str = " | ".join(context_info) if context_info else ""
            
            prompt = f"""Generate a concise 7-word or less title for this healthcare conversation.

Context: {context_str if context_str else 'General healthcare inquiry'}
User message: "{first_message}"

Rules:
- Maximum 7 words
- Clear and descriptive
- No quotation marks
- Professional healthcare context
- Title case

Return ONLY the title, nothing else."""
            
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=50,
                )
            )
            
            response = await model.generate_content_async(prompt)
            title = response.text.strip() if response.text else None
            
            if not title:
                return self._generate_fallback_title()
            
            title = title.strip('"\'')[:500]
            logger.info(f"Generated title with context: {title}")
            return title
            
        except Exception as e:
            logger.error(f"Contextual title generation failed: {e}")
            return self._generate_fallback_title()


# Type hints imports (deferred to avoid circular imports)
from typing import Optional, Dict, Any


# Create singleton instance
title_generator = TitleGeneratorService()
