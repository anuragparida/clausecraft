FROM node:20-alpine

WORKDIR /app

# pnpm via corepack (ships with the node base image).
RUN corepack enable && corepack prepare pnpm@9.7.0 --activate

# Install dependencies first so the install layer is cached when only
# source changes.
COPY package.json ./
RUN pnpm install --frozen-lockfile || pnpm install

# Now copy the rest of the source.
COPY . .

EXPOSE 15173

# Vite dev server. We bind to 0.0.0.0 (set in vite.config.ts) and use
# the env-injected port. `strictPort: true` means a port conflict
# fails loudly instead of silently falling back.
ENV VITE_PORT=15173
CMD ["pnpm", "run", "dev", "--host", "0.0.0.0", "--port", "15173"]
