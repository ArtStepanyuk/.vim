Vim synching between machines
```
git clone  https://github.com/ArtStepanyuk/vimSettings
ln -s ~/.vim/vimrc ~/.vimrc
ln -s ~/.vim/gvimrc ~/.gvimrc
cd ~/.vim
git submodule init
git submodule update
```
In case of LF troubles
find . -type f -exec dos2unix -k -s -o {} ';'

