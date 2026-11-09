# Apps

This directory contains two kinds of apps:

- `local-app` contains runnable code owned by this repository. Keep reusable business logic in [`libs/`](../libs/); use the app for its entry point, packaging, and deployment configuration.
- `service-app` contains configuration, provisioning files, or integration metadata for third-party software.

Run `make create-application` from the repository root, then select the app kind.

## Service app example

This example creates a Redis service app and mounts its configuration in the main Compose project. Start from the repository root. Docker and Docker Compose are required.

1. Run the application generator:

   ```shell
   make create-application
   ```

2. Select `service-app` at the app-kind prompt, then enter `redis` for the service app name.
3. Add `apps/redis/redis.conf`:

   ```text
   bind 0.0.0.0
   port 6379
   ```

4. Add this service to `docker-compose-scripts/copier-test-robm-compose-project/docker-compose.yml`. The volume path is relative to the Compose file's directory:

   ```yaml
   services:
     redis:
       image: redis:8
       command: ["redis-server", "/usr/local/etc/redis/redis.conf"]
       volumes:
         - ../../apps/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
   ```

5. In one terminal, start the main Compose project with `make docker-compose-up`. Select `copier-test-robm-compose-project` when prompted and leave the command running:

   ```shell
   make docker-compose-up
   ```

6. In a second terminal, run this command from the repository root. The Compose file identifies the project, and `redis` selects the service:

   ```shell
   docker compose -f docker-compose-scripts/copier-test-robm-compose-project/docker-compose.yml \
     exec redis sh -c 'redis-cli SET greeting "hello, world" && redis-cli --raw GET greeting'
   ```

   The command should print `OK` followed by:

   ```text
   hello, world
   ```
