import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

const gateway = process.env.GATEWAY_URL ?? 'http://127.0.0.1:8080';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: {
			'/api': { target: gateway, changeOrigin: true },
			'/ws': { target: gateway.replace(/^http/, 'ws'), ws: true }
		}
	}
});
