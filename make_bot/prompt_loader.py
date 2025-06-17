import logging
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

class ModelType(Enum):
    """Enum for different model types."""
    ORCHESTRATOR = "orchestrator"
    EXPERT = "expert"

# Directory containing prompt templates
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

def get_system_prompt(model_type: ModelType, context: str = "", **kwargs) -> str:
    """Get the formatted system prompt for the specified model type.
    
    Args:
        model_type: The type of model (ModelType.ORCHESTRATOR or ModelType.EXPERT)
        context: Context string to include in the prompt
        **kwargs: Additional template variables
        
    Returns:
        Formatted system prompt string
    """
    # Load template
    prompt_file = PROMPTS_DIR / f"{model_type.value}.txt"
    
    if not prompt_file.exists():
        logger.error(f"Prompt template not found: {prompt_file}")
        raise FileNotFoundError(f"Prompt template '{model_type.value}' not found at {prompt_file}")
    
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            template = f.read()
        logger.debug(f"Loaded prompt template: {model_type.value}")
    except Exception as e:
        logger.error(f"Error loading prompt template {model_type.value}: {e}")
        raise
    
    # Format context section based on model type
    if model_type == ModelType.ORCHESTRATOR:
        context_section = ""
        if context:
            context_section = f"""## Current Conversation Context

{context}

Use this context to maintain consistency and build upon previous discussions."""
    elif model_type == ModelType.EXPERT:
        context_section = context if context else "No additional context provided."
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    
    # Format template with parameters
    try:
        # Provide default values for common template variables
        defaults = {
            'context_section': context_section,
            'additional_instructions': '',
        }
        
        # Merge provided kwargs with defaults
        format_vars = {**defaults, **kwargs}
        
        formatted_prompt = template.format(**format_vars)
        logger.debug(f"Formatted prompt with parameters: {list(kwargs.keys())}")
        return formatted_prompt
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        raise ValueError(f"Missing required template variable: {e}")
    except Exception as e:
        logger.error(f"Error formatting prompt: {e}")
        raise

