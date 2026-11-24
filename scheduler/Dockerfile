FROM golang:1.24-alpine AS builder
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /scheduler ./cmd/scheduler

FROM alpine:3.21
RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /scheduler /usr/local/bin/scheduler
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/scheduler"]
