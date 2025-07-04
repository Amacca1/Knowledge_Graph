## Running the Project with Docker

This project is containerized using Docker and Docker Compose for easy setup and deployment. Below are the instructions and details specific to this project:

### Requirements & Dependencies
- **Python Version:** 3.13 (as specified in the Dockerfile: `python:3.13-slim`)
- **Dependencies:** All Python dependencies are listed in `requirement.txt` and installed in a virtual environment during the build process.

### Environment Variables
- The project includes a `userdetails.env` file for environment variables. By default, this is not loaded in the Docker Compose file. To use it, uncomment the `env_file: ./userdetails.env` line in the `docker-compose.yml` file.

### Build and Run Instructions
1. **Build and start the application:**
   ```sh
   docker compose up --build
   ```
   This will build the Docker image and start the `python-app` service.

2. **Access the application:**
   - The Flask app will be available at [http://localhost:5000](http://localhost:5000)

### Ports
- **5000:** The Flask application is exposed on port 5000 (as set in both the Dockerfile and Docker Compose).

### Special Configuration
- The application runs as a non-root user (`appuser`) inside the container for improved security.
- If you need to use environment variables, ensure you provide a `userdetails.env` file and uncomment the relevant line in `docker-compose.yml`.
- No additional services (like databases) are configured by default, but you can extend the `docker-compose.yml` as needed.

---

*For security information, see `SECURITY.md`.*