# The labelling page

`index.html`, `app.js` and `app.css` are served by `goldlabel._label` (offline, no external request).
`input.css` is the Tailwind entry point and is shipped only because it is the build input.

`app.css` is **generated** and committed, minified. Users never build anything. Rebuild it after
changing a class in `index.html` or `app.js`, with the Tailwind standalone CLI v4.3.3
(`tailwindcss-linux-x64` from https://github.com/tailwindlabs/tailwindcss/releases):

```
cd src/goldlabel/web
tailwindcss -i input.css -o app.css --minify --cwd .
sed -i '1s#^/\*!.*\*/##' app.css && sed -i '1{/^$/d}' app.css   # drop the licence banner: it holds a URL
```

Dark mode is Tailwind's default `dark:` variant, i.e. the `prefers-color-scheme` media query. Do not
add a class or data-attribute override, a toggle or a stored theme.
