#!/bin/bash -xue
rm -rf web-dist
rm pyweek-40.html pyweek-40.pyxapp
pyxel package . game.py
pyxel app2html pyweek-40.pyxapp
git clone --single-branch --branch gh-pages git@github.com:darabos/pyweek-40.git web-dist
cp pyweek-40.html web-dist/no-glow.html
cat pyweek-40.html | sed 's|src=".*pyxel.js"|src="wasm/pyxel.js"|g' > web-dist/index.html
echo '<title>Constrictor Constructor</title>' >> web-dist/index.html
echo '<title>Constrictor Constructor</title>' >> web-dist/no-glow.html
mkdir -p web-dist/wasm
cp ../pyxel/wasm/pyxel.js web-dist/wasm/
cp ../pyxel/wasm/pyxel.css web-dist/wasm/
cp ../pyxel/wasm/pyxel-2.5.7-cp38-abi3-emscripten_3_1_58_wasm32.whl web-dist/wasm/
mkdir -p web-dist/docs/images/
cp ../pyxel/docs/images/pyxel_icon_64x64.ico web-dist/docs/images/
cp ../pyxel/docs/images/pyxel_logo_76x32.png web-dist/docs/images/
cp ../pyxel/docs/images/touch_to_start_114x14.png web-dist/docs/images/
cp ../pyxel/docs/images/click_to_start_114x14.png web-dist/docs/images/
cp ../pyxel/docs/images/gamepad_cross_98x98.png web-dist/docs/images/
cp ../pyxel/docs/images/gamepad_button_98x98.png web-dist/docs/images/
cp ../pyxel/docs/images/gamepad_menu_92x26.png web-dist/docs/images/
cp ../pyxel/wasm/import_hook.py web-dist/wasm/
