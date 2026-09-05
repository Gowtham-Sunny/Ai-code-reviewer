FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV GROQ_API_KEY=""
ENV GITHUB_TOKEN=""
ENV GITHUB_REPO=""
ENV PR_NUMBER=""

# Run the code reviewer
CMD ["python", "src/main.py"]
