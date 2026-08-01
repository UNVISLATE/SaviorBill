FROM alpine:3.20 AS base

# Lua 5.4 + luarocks и тулчейн для сборки C-роков (luasocket/luasec/cjson).
RUN apk add --no-cache \
        lua5.4 lua5.4-dev luarocks5.4 \
        gcc musl-dev make \
        openssl-dev \
    && ln -sf /usr/bin/lua5.4 /usr/bin/lua \
    && luarocks-5.4 install lua-cjson \
    && luarocks-5.4 install luasocket \
    && luarocks-5.4 install luasec \
    && luarocks-5.4 install redis-lua \
    && luarocks-5.4 install luaossl

WORKDIR /app
COPY src/ /app/


# Тесты песочницы гоняются при сборке: падение = образ не собирается
# (тот же приём, что в src/Dockerfile и mediaworker/Dockerfile).
FROM base AS tests

COPY tests/ /app/tests/
RUN lua tests/sandbox_test.lua && touch /app/.tests-passed


FROM base AS runtime

COPY --from=tests /app/.tests-passed /app/.tests-passed

ENV VALKEY_HOST=valkey \
    VALKEY_PORT=6379 \
    VALKEY_DB=0 \
    LUA_TASK_STREAM=lua:tasks \
    LUA_RESP_STREAM=lua:results \
    LUA_GROUP=luaworkers \
    BILLING_URL=http://billing:8000

CMD ["lua", "main.lua"]