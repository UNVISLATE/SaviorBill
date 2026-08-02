import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // "примерыизсшм" — reference-примеры от пользователя (shadcn dashboard шаблоны),
  // не часть приложения и не участвуют в сборке; линтить их не нужно.
  //
  // fill-picker — вендорный color picker, поставленный через shadcn CLI
  // (amplo.ale.design). Это чужой код: правки в нём затрутся при следующем
  // обновлении компонента, поэтому под наши правила его не подгоняем.
  globalIgnores([
    'dist',
    'примерыизсшм',
    'src/components/shadsnui/fill-picker',
  ]),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
])
