FROM nginx:alpine

COPY services/web/static/ /usr/share/nginx/html/
COPY services/web/nginx.conf /etc/nginx/templates/default.conf.template

ENV CATALOG_URL=http://catalog:8001

EXPOSE 3000
