# imgur-pdfprint

Convert imgur.com albums to PDF files.

This tool has grown a bit over time and now supports the following sites:

- imgur.com
- simplecove.com

## Installation

Create a virtualenv and activate it:

    pyvenv-3.5 myvenv
    source myvenv/bin/activate

Install all python requirements:

    pip install -r requirements.txt


This tool requires asciidoctor being installed:

    gem install --pre asciidoctor-pdf


## Configuration

The API provided by imgur.com requires authentication. To use this tool you need to create
an account with imgur.com and export the "client id" and "client secret" of that account as 
environment variables. Example (bash):

    export IMGUR_CLIENT_ID="xxxx"
    export IMGUR_CLIENT_SECRET="yyyy"


## Usage

    python ./pdfprint.py --url http://imgur.com/a/XNM1x


The PDF file will be put into the current directory.
