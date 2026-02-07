FROM nginx:alpine

COPY services/web/static/ /usr/share/nginx/html/
COPY services/web/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000
