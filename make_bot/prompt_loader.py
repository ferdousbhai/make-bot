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

def _format_context_section(model_type: ModelType, context: str) -> str:
    """Format context section based on model type."""
    if model_type == ModelType.ORCHESTRATOR and context:
        return f"""## Current Conversation Context

{context}

Use this context to maintain consistency and build upon previous discussions."""
    elif model_type == ModelType.EXPERT:
        return context or "No additional context provided."
    return ""

def _load_prompt_template_from_file(model_type: ModelType) -> str:
    """Load prompt template from file based on model type."""
    prompt_file = PROMPTS_DIR / f"{model_type.value}.txt"

    if not prompt_file.exists():
        logger.error(f"Prompt template not found: {prompt_file}")
        raise FileNotFoundError(f"Prompt template '{model_type.value}' not found at {prompt_file}")

    try:
        template = prompt_file.read_text(encoding='utf-8')
        logger.debug(f"Loaded prompt template: {model_type.value}")
        return template
    except Exception as e:
        logger.error(f"Error loading prompt template {model_type.value}: {e}")
        raise

def get_system_prompt(model_type: ModelType, context: str = "", **kwargs) -> str:
    """Get the formatted system prompt for the specified model type.

    Args:
        model_type: The type of model (ModelType.ORCHESTRATOR or ModelType.EXPERT)
        context: Context string to include in the prompt
        **kwargs: Additional template variables

    Returns:
        Formatted system prompt string
    """
    template = _load_prompt_template_from_file(model_type)

    # Prepare format variables with defaults
    template_variables = {
        'context_section': _format_context_section(model_type, context),
        'additional_instructions': '',
        **kwargs
    }

    try:
        formatted_prompt = template.format(**template_variables)
        logger.debug(f"Formatted prompt with parameters: {list(kwargs.keys())}")
        return formatted_prompt
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        raise ValueError(f"Missing required template variable: {e}")
    except Exception as e:
        logger.error(f"Error formatting prompt: {e}")
        raise

