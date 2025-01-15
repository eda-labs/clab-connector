# OpenAPI specification

## Fetching schema from EDA

> note, that `/auth/login` endpoint will be deprecated in the future. See <https://docs.eda.dev/development/api/>

```
EDA_TOKEN=$(curl -s -k -X POST https://eda-api-url/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password":"admin"}')

curl -k https://devbox/openapi/v3/core \
  -H "Authorization: Bearer $EDA_TOKEN" \
  -H 'Content-Type: application/json' > assets/openapi/<version>/core.json
```

## Rendering schema with swagger ui

```bash
sudo docker run -p 8080:8080 -e SWAGGER_JSON=/api/core.json -v $(pwd)/assets/openapi/v24.12.1:/api swaggerapi/swagger-ui
```

Access schema ui at <http://localhost:8080/>
