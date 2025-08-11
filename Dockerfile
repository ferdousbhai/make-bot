# Use Python 3.13 slim image
FROM python:3.13-slim

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy uv configuration files first for better Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ ./app/
COPY run.py ./

# Expose port (Railway will handle this, but good practice)
EXPOSE 8000

# Use uv to run the application
CMD ["uv", "run", "run.py"]