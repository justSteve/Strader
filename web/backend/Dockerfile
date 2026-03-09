FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install schwab-py from mounted volume at runtime
RUN echo '#!/bin/bash\nif [ -d /app/schwab-py ]; then pip install -e /app/schwab-py 2>/dev/null; fi\nexec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
