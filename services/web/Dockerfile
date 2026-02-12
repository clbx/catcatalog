FROM nginx:alpine

ARG VERSION=dev

COPY services/web/static/ /usr/share/nginx/html/
COPY services/web/nginx.conf /etc/nginx/templates/default.conf.template

RUN sed -i "s/__VERSION__/${VERSION}/g" /usr/share/nginx/html/index.html

ENV CATALOG_URL=http://catalog:8001

EXPOSE 3000
