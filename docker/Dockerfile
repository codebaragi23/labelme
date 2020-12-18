FROM codebaragi23/ubuntu18.04-python3.6.9:opencv4.2.0
LABEL maintainer "codebaragi23 (codebaragi23@gmail.com)"

COPY ./requirements.txt /requirements.txt
COPY ./install_korean-language.sh /install_korean-language.sh

ENV DEBIAN_FRONTEND noninteractive

RUN \
  apt-get update -qq && \
  apt-get install -qq -y \
    libgl1-mesa-glx \
    libgdal-dev
  && rm -rf /var/lib/apt/lists/*

RUN /bin/bash install_korean-language.sh

RUN pip3 install -U -r requirements.txt
# RUN rm /requirements.txt
# RUN pip3 install -v git+https://github.com/codebaragi23/mindAT.git

RUN mkdir /root/workspace
# ENV LANG en-US

WORKDIR /root/workspace
# ENTRYPOINT [ "mindAT" ]
