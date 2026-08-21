"""
Constrained LLM extraction for symptom categorization
Maps free-text chief complaint to YAML-defined categories

This prevents hallucination by:
1. Providing exact allowed list to LLM
2. Validating LLM output against allowed categories
3. Fallback to keyword matching if LLM fails or produces invalid category
"""
import logging
from typing import Optional, Dict, Any
import google.generativeai as genai
from app.config import settings
from app.constants.symptom_categories import (
    ALLOWED_SYMPTOM_CATEGORIES,
    CATEGORY_KEYWORDS,
    CATEGORY_DESCRIPTIONS,
    SAFETY_CATEGORIES
)

logger = logging.getLogger(__name__)


class SymptomClassifier:
    """Constrained LLM-based symptom category extraction with validation"""
    
    def __init__(self):
        """Initialize Gemini model if API key available"""
        self.model = None
        if settings.google_api_key:
            try:
                genai.configure(api_key=settings.google_api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                logger.info("Symptom classifier initialized with Gemini LLM")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}, using keyword fallback only")
                self.model = None
        else:
            logger.warning("GOOGLE_API_KEY not set, using keyword fallback only")
    
    def classify_complaint(
        self, 
        chief_complaint: str, 
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classify free-text chief complaint into one of the allowed categories
        
        Args:
            chief_complaint: Patient's description (e.g., "I have a bad headache")
            additional_context: Optional context (e.g., "patient has diabetes")
        
        Returns:
            {
                "category": "mild_general_symptom",
                "confidence": "high" | "medium" | "low",
                "method": "llm" | "keyword" | "fallback",
                "is_safety_category": bool
            }
        """
        if not chief_complaint or not chief_complaint.strip():
            logger.warning("Empty chief complaint, using default category")
            return self._build_result("mild_general_symptom", "low", "fallback")
        
        # Step 1: Try constrained LLM extraction (if available)
        if self.model:
            try:
                llm_result = self._llm_extract(chief_complaint, additional_context)
                
                # Step 2: Validate LLM output
                if llm_result["category"] in ALLOWED_SYMPTOM_CATEGORIES:
                    logger.info(
                        f"LLM classified '{chief_complaint[:50]}...' → '{llm_result['category']}'"
                    )
                    return self._build_result(llm_result["category"], "high", "llm")
                else:
                    logger.warning(
                        f"LLM returned invalid category '{llm_result['category']}', "
                        f"falling back to keywords"
                    )
            
            except Exception as e:
                logger.warning(f"LLM extraction failed: {e}, falling back to keywords")
        
        # Step 3: Fallback to keyword matching
        keyword_result = self._keyword_match(chief_complaint)
        if keyword_result:
            logger.info(
                f"Keyword matched '{chief_complaint[:50]}...' → '{keyword_result}'"
            )
            return self._build_result(keyword_result, "medium", "keyword")
        
        # Step 4: Default fallback
        logger.warning(
            f"No match for '{chief_complaint[:50]}...', using default 'mild_general_symptom'"
        )
        return self._build_result("mild_general_symptom", "low", "fallback")
    
    def _build_result(self, category: str, confidence: str, method: str) -> Dict[str, Any]:
        """Build standardized result dict"""
        return {
            "category": category,
            "confidence": confidence,
            "method": method,
            "is_safety_category": category in SAFETY_CATEGORIES
        }
    
    def _llm_extract(
        self, 
        chief_complaint: str, 
        additional_context: Optional[str]
    ) -> Dict[str, str]:
        """Use LLM to extract category from complaint"""
        
        # Build constrained prompt with allowed categories
        category_list = "\n".join([
            f"- {cat}: {CATEGORY_DESCRIPTIONS.get(cat, '')}"
            for cat in ALLOWED_SYMPTOM_CATEGORIES
        ])
        
        prompt = f"""You are a medical triage assistant. Classify this patient's chief complaint into EXACTLY ONE category from the list below.

CHIEF COMPLAINT: "{chief_complaint}"

{f"ADDITIONAL CONTEXT: {additional_context}" if additional_context else ""}

ALLOWED CATEGORIES:
{category_list}

CRITICAL RULES:
1. Output ONLY the category name (e.g., "mild_general_symptom")
2. Do NOT add explanation, punctuation, or extra text
3. The category MUST be from the list above - do not invent new categories
4. If unsure, choose "mild_general_symptom"
5. Match based on symptom description, not severity words

CATEGORY:"""
        
        # Call LLM
        response = self.model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # Low temperature for consistency
                max_output_tokens=50,
            )
        )
        
        # Extract and clean output
        category = response.text.strip().lower()
        
        # Remove common punctuation/quotes
        category = category.replace('"', '').replace("'", '').replace('.', '').replace(',', '')
        
        return {"category": category}
    
    def _keyword_match(self, chief_complaint: str) -> Optional[str]:
        """Fallback keyword matching with scoring"""
        complaint_lower = chief_complaint.lower()
        
        # Score each category
        scores = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in complaint_lower)
            if score > 0:
                scores[category] = score
        
        # Return highest scoring category
        if scores:
            best_category = max(scores, key=scores.get)
            return best_category
        
        return None


# Singleton instance
symptom_classifier = SymptomClassifier()
