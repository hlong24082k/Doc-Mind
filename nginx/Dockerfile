FROM node:22-alpine AS build
WORKDIR /client
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ .
ENV VITE_API_BASE_URL=/api
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /client/dist /usr/share/nginx/html
