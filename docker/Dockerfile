FROM ulikoehler/ubuntu-python3-opencv
LABEL maintainer "codebaragi23 (codebaragi23@gmail.com)"

COPY ./requirements.txt /requirements.txt
ENV DEBIAN_FRONTEND=noninteractive
RUN \
  apt-get update -qq && \
  apt-get install -qq -y \
    git \
    python3-pip \
    python3-matplotlib \
    python3-pyqt5 \
    python3-numpy \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install -U -r requirements.txt

RUN pip3 install -v git+https://github.com/codebaragi23/labelme.git

RUN mkdir /root/workdir

ENV LANG en-US

WORKDIR /root/workdir
ENTRYPOINT [ "labelme" ]
