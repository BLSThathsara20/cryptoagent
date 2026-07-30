FROM node:18-bookworm-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install && npm install @rollup/rollup-linux-x64-gnu --no-save

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
