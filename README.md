#My vim setup for js development
1 tern support
2 ctags support
3 eslint support
4 YCM
and much more all what you wanted to do with your vim on new machine but never had time

Vim synching between machines
Get vim with ctrlP support from AUR or add ctrlP to submodules itself
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

