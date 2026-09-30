# Production-Grade URL Shortener

A production-ready URL Shortener built using Python and FastAPI. The application provides secure URL shortening, analytics, caching, monitoring, and deployment support using modern backend technologies.

## Features

- Create short URLs
- Redirect using short URLs
- URL analytics
- Redis caching
- Background tasks with Celery
- PostgreSQL database
- API authentication
- Rate limiting
- Docker support
- Health checks
- Metrics monitoring
- Automated testing

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Redis
- Celery
- Docker
- Docker Compose
- Pytest
- GitHub Actions

## Project Structure

```
app/
tests/
scripts/
docs/
main.py
requirements.txt
Dockerfile
docker-compose.yml
README.md
```

## Installation

git clone https://github.com/samaspoorthireddy/url-shortener.git

cd url-shortener

pip install -r requirements.txt

## Run the Application

```bash
python main.py
```

Or using Docker:

```bash
docker-compose up --build
```

## Testing

```bash
pytest
```

## Author

Spoorthi Reddy Sama
