from app import mythic, db_objects
from sanic.response import json
from sanic_jwt.decorators import scoped, inject_user
import app.database_models.model as db_model
from sanic.exceptions import abort
from math import ceil
from peewee import fn


@mythic.route(mythic.config['API_BASE'] + "/event_message", methods=['POST'])
@inject_user()
@scoped('auth:user')
async def add_event_message(request, user):
    if user['auth'] not in ['access_token', 'apitoken']:
        abort(status_code=403, message="Cannot access via Cookies. Use CLI or access via JS in browser")
    if user['view_mode'] == 'spectator':
        return json({'status': 'error', 'error': 'Spectators cannot send messages'})
    try:
        query = await db_model.operator_query()
        operator = await db_objects.get(query, username=user['username'])
        query = await db_model.operation_query()
        operation = await db_objects.get(query, name=user['current_operation'])
        data = request.json
        if 'message' not in data:
            return json({'status': 'error', 'error': 'message is required'})
        await db_objects.create(db_model.OperationEventLog, operator=operator, operation=operation,
                                message=data['message'])
        return json({'status': 'success'})
    except Exception as e:
        return json({'status': 'error', 'error': str(e)})


@mythic.route(mythic.config['API_BASE'] + "/event_message/<eid:int>", methods=['PUT'])
@inject_user()
@scoped('auth:user')
async def edit_event_message(request, user, eid):
    if user['auth'] not in ['access_token', 'apitoken']:
        abort(status_code=403, message="Cannot access via Cookies. Use CLI or access via JS in browser")
    if user['view_mode'] == 'spectator':
        return json({'status': 'error', 'error': 'Spectators cannot edit messages'})
    try:
        query = await db_model.operator_query()
        operator = await db_objects.get(query, username=user['username'])
        query = await db_model.operation_query()
        operation = await db_objects.get(query, name=user['current_operation'])
        data = request.json
        query = await db_model.operationeventlog_query()
        msg = await db_objects.get(query, id=eid, operation=operation)
        if 'message' not in data and 'resolved' not in data:
            return json({'status': 'error', 'error': 'message or resolve status is required'})
        else:
            if user['admin'] or msg.operator == operator or operation.name in user['admin_operations']:
                if 'message' in data:
                    msg.message = data['message']
                if 'resolved' in data:
                    msg.resolved = data['resolved']
                await db_objects.update(msg)
            else:
                return json({'status': 'error', 'error': "You must be the author of the message, a global admin, or operation admin to edit that message"})
        return json({'status': 'success', **msg.to_json()})
    except Exception as e:
        return json({'status': 'error', 'error': str(e)})


@mythic.route(mythic.config['API_BASE'] + "/event_message/delete", methods=['POST'])
@inject_user()
@scoped('auth:user')
async def remove_event_messagse(request, user):
    if user['auth'] not in ['access_token', 'apitoken']:
        abort(status_code=403, message="Cannot access via Cookies. Use CLI or access via JS in browser")
    if user['view_mode'] == 'spectator':
        return json({'status': 'error', 'error': 'Spectators cannot remove messages'})
    try:
        query = await db_model.operator_query()
        operator = await db_objects.get(query, username=user['username'])
        query = await db_model.operation_query()
        operation = await db_objects.get(query, name=user['current_operation'])
        data = request.json
        query = await db_model.operationeventlog_query()
        not_authorized = False
        for e in data['messages']:
            # given an array of message ids to delete, try to delete them all
            msg = await db_objects.get(query, id=e, operation=operation)
            if user['admin'] or msg.operator == operator or operation.name in user['admin_operations']:
                msg.deleted = True
                await db_objects.update(msg)
            else:
                not_authorized = True
        if not_authorized:
            return json({'status': 'error', 'error': "Failed to delete some messages since you're not authorized"})
        else:
            return json({'status': 'success'})
    except Exception as e:
        return json({'status': 'error', 'error': str(e)})


@mythic.route(mythic.config['API_BASE'] + "/event_message/search", methods=['POST'])
@inject_user()
@scoped(['auth:user', 'auth:apitoken_user'], False)  # user or user-level api token are ok
async def search_event_message(request, user):
    if user['auth'] not in ['access_token', 'apitoken']:
        abort(status_code=403, message="Cannot access via Cookies. Use CLI or access via JS in browser")
    try:
        query = await db_model.operation_query()
        operation = await db_objects.get(query, name=user['current_operation'])
        query = await db_model.operationeventlog_query()
    except Exception as e:
        return json({'status': 'error', 'error': 'failed to find that file browsing object in your current operation'})
    try:
        data = request.json
        count = await db_objects.count(query.where(
            (db_model.OperationEventLog.operation == operation) &
            (fn.encode(db_model.OperationEventLog.message, 'escape').regexp(data['search']))).distinct())
        if 'page' not in data:
            # allow a blanket search to still be performed
            responses = await db_objects.execute(query.where(
            (db_model.OperationEventLog.operation == operation) &
            (fn.encode(db_model.OperationEventLog.message, 'escape').regexp(data['search']))).distinct())
            data['page'] = 1
            data['size'] = count
        else:
            if 'page' not in data or 'size' not in data or int(data['size']) <= 0 or int(data['page']) <= 0:
                return json({'status': 'error', 'error': 'size and page must be supplied and be greater than 0'})
            data['size'] = int(data['size'])
            data['page'] = int(data['page'])
            if data['page'] * data['size'] > count:
                data['page'] = ceil(count / data['size'])
                if data['page'] == 0:
                    data['page'] = 1
            responses = await db_objects.execute(query.where(
            (db_model.OperationEventLog.operation == operation) &
            (fn.encode(db_model.OperationEventLog.message, 'escape').regexp(data['search']))).distinct().paginate(data['page'], data['size']))
        output = []
        for r in responses:
            rjson = r.to_json()
            output.append(rjson)
        return json(
            {'status': 'success', 'output': output, 'total_count': count, 'page': data['page'], 'size': data['size']})
    except Exception as e:
        print(e)
        return json({'status': 'error', 'error': str(e)})
