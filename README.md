# Audiobookshelf OPDS Bridge

OPDS bridge for [Audiobookshelf](https://www.audiobookshelf.org/), allowing you to use your audiobook library through the OPDS protocol in any compatible readers and applications.

## Features

- Full OPDS protocol support
- Book search via OpenSearch
- Basic Auth and token-based authentication

## Tested With

- [FBReader](https://fbreader.org/)
- [Moon+ Reader](https://moondownload.com/)

## Requirements

- Python 3.13+
- Audiobookshelf server with API token

## Installation and Running

### Local Running

1. Clone the repository:
```bash
git clone https://github.com/bne2hm/abs-opds-bridge.git
cd abs-opds-bridge
```

2. Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. Create a `.env` file with settings:
```env
ABS_BASE=http://localhost:port
ABS_TOKEN=your_audiobookshelf_token
OPDS_BASIC_USER=your_opds_username
OPDS_BASIC_PASS=your_opds_password
```

4. Run the application:
```bash
uvicorn opds_bridge.main:app --host 0.0.0.0 --port 8000
```

### Running in Docker

1. Build the image:
```bash
docker build -t abs-opds-bridge .
```

2. Run the container:
```bash
docker run -d -p 8000:8000 \
  -e ABS_BASE="http://your-audiobookshelf:13378" \
  -e ABS_TOKEN="your-token-here" \
  -e OPDS_BASIC_USER="username" \
  -e OPDS_BASIC_PASS="password" \
  --name abs-opds-bridge \
  abs-opds-bridge
```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `ABS_BASE` | URL of your Audiobookshelf server | Yes | `http://localhost:13378` |
| `ABS_TOKEN` | Audiobookshelf API token | Yes | - |
| `OPDS_BASIC_USER` | Username for Basic Auth | No | - |
| `OPDS_BASIC_PASS` | Password for Basic Auth | No | - |

## License

MIT
