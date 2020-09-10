apt-get install -qq -y \
     locales \
     language-pack-ko \
     fonts-nanum fonts-nanum-extra nabi \
  && locale-gen ko_KR.UTF-8 \
  && update-locale LANG=ko_KR.UTF-8 LC_MESSAGES=POSIX \
  && echo "export XMODIFIERS=@im=nabi" >> /root/.bashrc

