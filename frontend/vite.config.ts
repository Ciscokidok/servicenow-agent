import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  css: {
    postcss: {
      plugins: [
        {
          postcssPlugin: 'internal:virtual-env',
          OnceExit(css) {
            css.walkDecls('background-image', (decl) => {
              if (decl.value.includes('url')) {
                decl.value = decl.value.replace(
                  /url\((['"]?)(.*?)\1\)/g,
                  (match, quote, url) => {
                    if (!url.startsWith('data:') && !url.startsWith('http')) {
                      return `url(${quote}${new URL(url, 'http://localhost:3000').href}${quote})`
                    }
                    return match
                  }
                )
              }
            })
          }
        }
      ]
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: true,
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html')
      }
    }
  }
})
