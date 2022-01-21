#
# This software is Copyright ©️ 2020 The University of Southern California. All Rights Reserved.
# Permission to use, copy, modify, and distribute this software and its documentation for educational, research and non-profit purposes, without fee, and without a written agreement is hereby granted, provided that the above copyright notice and subject to the full license file found in the root of this software deliverable. Permission to make commercial use of this software may be obtained by contacting:  USC Stevens Center for Innovation University of Southern California 1150 S. Olive Street, Suite 2300, Los Angeles, CA 90115, USA Email: accounting@stevens.usc.edu
#
# The full terms of this copyright and license should always be found in the root directory of this software deliverable as "license.txt" and if these terms are not found with this software, please contact the USC Stevens Center for the full license.
#
import json
from functools import wraps
import jsonschema
from jsonschema import validate
from flask import request
import logging


def validate_json(json_schema):
    def validate_json_wrapper(f):
        @wraps(f)
        def json_validated_function(*args, **kwargs):
            try:
                if not json_schema:
                    raise Exception("'json_schema' param not provided to validator")
                body = request.form.get("body", {})
                if body:
                    json_body = json.loads(body)
                else:
                    json_body = request.json
                if not json_body:
                    raise Exception("missing required param body")
                validate(instance=json_body, schema=json_schema)
                return f(json_body, *args, **kwargs)
            except jsonschema.exceptions.ValidationError as err:
                logging.error(msg=err)
                raise Exception(err)

        return json_validated_function

    return validate_json_wrapper
