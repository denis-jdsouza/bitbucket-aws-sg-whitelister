FROM python:3.10.3-alpine3.14 as base
FROM base as builder
COPY requirements.txt /requirements.txt
RUN pip install --user --no-warn-script-location -r requirements.txt

FROM base
COPY --from=builder /root/.local /root/.local
WORKDIR /app
COPY bitbucket-aws-sg-whitelister.py .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "bitbucket-aws-sg-whitelister.py"]
