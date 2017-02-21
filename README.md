#My vim setup for js development

In the end you will get a very nice looking neovim which is ready to do all you for js/rails development

1 tern support

2 ctags support

3 eslint support

4 YCM

and much more all what you wanted to do with your vim on new machine but never had time

Vim synching between machines
Get vim with ctrlP support from AUR or add ctrlP to submodules itself
Before install make sure you have node modules required for eslint and beautify

Some modules like tern will require extra stuff, be sure to check refference to actual repos of plugins which dont work

npm -g i js-beautify

npm -g i typescript
```
git clone  https://github.com/ArtStepanyuk/vimSettings
ln -s ~/.vim/vimrc ~/.vimrc
ln -s ~/.vim/gvimrc ~/.gvimrc
cd ~/.vim
cp -a vimSettings/ ~ ./.vim/
git submodule init
git submodule update
```
In case of LF troubles

find . -type f -exec dos2unix -k -s -o {} ';'

